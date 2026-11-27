# Configuration API or Package Changes

## Lesson Objectives

When upgrading Spring REST Docs, some errors appear immediately at compile time because classes, methods, constructors, or packages have changed. Other issues only surface when running tests or generating documentation: filters are not attached in the right place, configurers use the wrong integration, snippets are not generated, or preprocessing no longer takes effect.

This lesson belongs to the **Upgrade** chapter of the **SPRING_REST_DOCS** module: generating verifiable REST API documentation through HTTP tests with **MockMvc**, **WebTestClient**, or **REST Assured**; producing snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation; and integrating it into the build and CI.

After this lesson, you will be able to:

- Classify errors caused by packages, API signatures, dependencies, or runtime behavior.
- Verify new APIs using Javadoc and sources for the exact target version.
- Migrate documentation configuration, filters, and preprocessors in a controlled manner.
- Update imports and dependencies without mixing versions across integration modules.
- Preserve assertions, document identifiers, descriptors, and output contracts.
- Verify snippets and documentation after migration.
- Organize small, focused changes for easy review and rollback.

## 1. Why Do Configuration API Changes Cause Errors?

An upgrade can change:

- Class packages or which artifact contains a class.
- Method names, overloads, generic types, or return types.
- Constructors replaced by factories/configurers.
- Constructor or method visibility.
- How documentation filters are attached to MockMvc, WebTestClient, or REST Assured.
- Preprocessor types accepted for requests and responses.
- Default behavior or when snippets are written.

Not every change is a breaking change. A method may simply be deprecated before being removed in the next major release. Therefore, identify which category an error belongs to before editing code.

## 2. Classifying Errors Before Migration

| Symptom | Possible Root Cause Group | Where to Check First |
| --- | --- | --- |
| package does not exist | Class moved packages or missing artifact | Javadoc/package index and dependency tree |
| cannot find symbol | Method/class renamed, removed, or improperly imported | Exact-version Javadoc, compiler output |
| method cannot be applied | Signature/overload/generic type changed | Method declaration and type inference |
| NoSuchMethodError | Runtime version differs from compile-time version | Dependency resolution and classpath |
| ClassNotFoundException | Artifact missing from runtime/test classpath | Dependency tree and module dependencies |
| Tests run but no snippets produced | Filter/configurer not attached or operation result not consumed | Test setup and output directory |
| Incorrect snippet content | Preprocessor/template/default behavior changed | Operation data and generated output |
| Asciidoctor cannot find file | Snippet ID, file name, or task dependency changed | Generated snippets and include paths |

Do not fix every error by adding imports or pinning a dependency at random. With NoSuchMethodError, compilation may have succeeded while runtime loads a different class version; find which dependency selected that version.

## 3. Verifying Packages and APIs for the Exact Version

Before changing code, confirm the resolved version in the project. The `current` documentation may describe APIs newer than the version you are using.

Verification workflow:

1. Identify the artifact containing the failing class.
2. Confirm the resolved compile and test runtime versions.
3. Open the Javadoc or source JAR for that exact version.
4. Locate the old class and any replacement class/method (if present).
5. Read Deprecated, Since, and migration notes.
6. Check changes in related integration modules.
7. Apply minimal fixes and recompile the test module.

For example, when an import can no longer be found:

~~~java
import org.springframework.restdocs.mockmvc.MockMvcRestDocumentation;
~~~

Do not guess a new package from the class name. Look up the class in the Javadoc/source artifact of the target version. If the class moved to another artifact, update the corresponding dependency; if the class was replaced, read the migration docs to adopt the supported API.

Packages to check depending on the integration:

- org.springframework.restdocs.mockmvc
- org.springframework.restdocs.webtestclient
- org.springframework.restdocs.restassured
- org.springframework.restdocs.operation.preprocess
- org.springframework.restdocs.payload

These are the API areas to inspect, not a claim that every class in them has changed packages between versions.

## 4. Checking Dependencies and Artifacts

Spring REST Docs splits integrations by test harness:

| Artifact | Purpose |
| --- | --- |
| spring-restdocs-core | Core API and operation/snippet model |
| spring-restdocs-mockmvc | MockMvc integration |
| spring-restdocs-webtestclient | WebTestClient integration |
| spring-restdocs-restassured | REST Assured integration |
| spring-restdocs-asciidoctor | Extension supporting Asciidoctor |

Keep artifacts in the same release line synchronized according to official guidance. Do not add a new integration artifact if tests do not use it, and do not mix core and integration modules across different versions without explicit instruction.

### 4.1. Checking with Gradle

~~~powershell
./gradlew dependencyInsight --dependency spring-restdocs --configuration testCompileClasspath
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
~~~

Check both compile and runtime because the two classpaths can resolve differently. If the project uses a version catalog, platform, or constraints, locate where the version is managed instead of editing a generated or downstream dependency directly.

### 4.2. Checking with Maven

~~~bash
mvn dependency:tree -Dincludes=org.springframework.restdocs
mvn help:effective-pom
~~~

dependency:tree reveals the actual artifacts; effective-pom helps identify versions managed by a parent POM, BOM, or dependencyManagement. When encountering linkage errors, inspect the dependency trees for Spring Framework, Spring Test, and REST Assured as well.

## 5. Migrating MockMvc Configuration

MockMvc typically attaches REST Docs via MockMvcRestDocumentation.documentationConfiguration(...) when building MockMvc. Example:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation))
    .build();
~~~

The operation test records the snippet:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42))
    .andExpect(status().isOk())
    .andDo(document("orders-get"));
~~~

When upgrading, confirm:

- Whether documentationConfiguration(...) still accepts the same context provider.
- Whether the configurer changed its fluent API or return type.
- Whether a custom MockMvcBuilder is overriding a shared configurer.
- That both test slices and full application context tests attach REST Docs properly.
- That document(...) is called after necessary assertions.

If the project has a base test or factory that builds MockMvc, update it in one place and run a representative test before rolling out further.

## 6. Migrating WebTestClient Configuration

WebTestClient has its own integration configurer:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .configureClient()
    .filter(
        WebTestClientRestDocumentation.documentationConfiguration(
            restDocumentation
        )
    )
    .build();
~~~

Operation:

~~~java
client.get()
    .uri("/api/orders/{id}", 42)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .consumeWith(
        WebTestClientRestDocumentation.document("orders-get")
    );
~~~

When the configuration API changes, also verify the bind mode:

- bindToApplicationContext uses the application context.
- bindToController suits testing one or a few specific controllers.
- bindToRouterFunction uses functional endpoints.
- bindToServer calls an already running server.

Switching bind modes can alter the scope of middleware, filters, codecs, and network behavior being tested. Do not treat this as a purely syntactic change.

## 7. Migrating REST Assured Configuration

REST Assured integrates with Spring REST Docs via a filter:

~~~java
RequestSpecification documentationSpec =
    new RequestSpecBuilder()
        .addFilter(
            RestAssuredRestDocumentation.documentationConfiguration(
                restDocumentation
            )
        )
        .build();
~~~

Test operation:

~~~java
given(documentationSpec)
    .filter(document("orders-get"))
    .when()
    .get("/api/orders/{id}", 42)
    .then()
    .statusCode(200);
~~~

When upgrading, confirm that the package of RestAssuredRestDocumentation and the filter are still accurate; RequestSpecification is used in the executed request; the documentation filter is attached in the right position; the REST Assured version is compatible with the Spring REST Docs integration; and response assertions still run and fail tests when the contract is not met.

If a test uses multiple filters, check the order and side effects of each filter. Do not alter filter order merely to make snippets match the baseline if doing so changes test behavior.

## 8. Migrating Preprocessors and Custom Snippets

Preprocessors can be configured per request/response or on the documentation configurer. When method signatures change, check the exact types required by the integration.

~~~java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token"))
    .andExpect(status().isOk())
    .andDo(document("profile-get",
        preprocessRequest(removeHeaders("Authorization")),
        preprocessResponse(prettyPrint())
    ));
~~~

When upgrading:

- Verify imports for Preprocessors, request/response preprocessor interfaces, and helper methods.
- Check overloads of preprocessRequest(...)/preprocessResponse(...).
- Verify whether default preprocessors on the configurer retain the same behavior.
- Check whether custom OperationPreprocessor implementations need interface or method updates.
- Confirm sensitive headers/tokens remain masked in snippets.

Custom snippet templates must also be checked. Template APIs may still compile while template output changes due to new models/attributes. Regenerate representative snippets and compare contents instead of only confirming the task succeeds.

## 9. Preserving Contracts and Document Identifiers

When updating configuration APIs or packages, do not simultaneously change:

- Document identifiers such as orders-get.
- Path/query parameter names.
- Field descriptors and contract descriptions.
- Preprocessor masking rules.
- Template formats and output directories.

Keeping these elements stable isolates the impact of the migration. If you must change one of them, document the reason clearly and update the corresponding snippet includes.

AsciiDoc documentation example:

~~~asciidoc
include::{snippets}/orders-get/http-request.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]
~~~

After upgrading, verify these files are still generated with the expected identifier and file names. If snippet names change due to version/template updates, update includes based on actual output rather than guessing file names.

## 10. Handling Compiler Errors Efficiently

When the compiler reports cannot find symbol, handle it in order:

1. Read the very first error completely, identifying the symbol and source file.
2. Check the resolved dependency version.
3. Look up the class/method in the Javadoc/source JAR of the target version.
4. Compare the old and new signatures.
5. Update imports, dependencies, or call sites according to the root cause.
6. Recompile the affected test source.
7. Run the operation test and inspect the snippet.

Do not edit many files at once before knowing the exact API change. For NoSuchMethodError, do not just change imports: inspect the runtime classpath and eliminate coexisting duplicate versions.

## 11. Comparing Output After Migration

Run tests into a new snippet directory separated from the old output. Compare:

| Content | What to Confirm |
| --- | --- |
| HTTP request | Method, URI, query, headers, and body |
| HTTP response | Status, headers, and body |
| Parameter snippets | Names, descriptions, and encoding |
| Field snippets | Field paths, types, descriptions, optional |
| Preprocessing | Pretty-print, masking, normalization |
| Custom snippets | Templates, attributes, and rendered output |
| Final documentation | Include paths, links, TOC, and Asciidoctor/Markdown output |

Some differences in header ordering or whitespace may be formatting only. Differences in status, fields, content type, parameters, or masked values require investigation.

For JSON, compare structurally if property order is not part of the contract. For headers, distinguish headers added automatically by the test client from headers actually guaranteed by the API.

## 12. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Package no longer exists | Class moved modules/packages or missing dependency | Check exact-version Javadoc/source and verify artifacts |
| Method does not accept old arguments | Overload or generic signature changed | Use the version-accurate signature; do not cast arbitrarily |
| NoSuchMethodError | Compile/runtime dependency mismatch | Run dependencyInsight or dependency tree |
| MockMvc generates no snippets | Configurer not applied to the builder in use | Check factories/base tests and actual builder |
| WebTestClient does not record operation | Filter/consumeWith placed in the wrong position | Check documentation filter and exchange chain |
| REST Assured does not write snippets | Filter not attached to the executed request specification | Check the spec passed into given(...) |
| Preprocessor stops masking tokens | Import, overload, or configuration changed | Inspect snippet output and new API |
| Asciidoctor reports missing include | Document ID/snippet name/output directory changed | Cross-check generated-snippets and update includes |
| Custom snippet renders incorrectly | Template model or template format changed | Compare templates and snippet outputs |
| Some tests still use old API | Configuration duplicated across multiple base tests | Centralize configuration and search all call sites |

## 13. Hands-On Exercise

Choose a REST Docs test currently using MockMvc, WebTestClient, or REST Assured.

Requirements:

1. Record the current imports, configurer/filter, preprocessors, and document identifier.
2. Choose a target version and verify APIs using Javadoc/sources for that exact version.
3. Create a dedicated migration branch and update dependencies and related artifacts synchronously.
4. Update packages/imports/signatures to the new API without changing the operation contract.
5. Run tests and confirm request/response assertions remain complete.
6. Generate snippets into a new directory and compare against the baseline.
7. Render Asciidoctor/Markdown and confirm no includes are broken.
8. Run CI with both tests and documentation generation tasks.

**Completion criteria:** no unsupported legacy APIs/packages remain; dependencies resolve consistently; tests pass; snippets and documentation reflect the same contract; output changes are explained and reviewable.

## Key Takeaways

When upgrading Spring REST Docs, distinguish between package/import errors, method signature changes, dependency mismatches, and runtime behavior changes. Verify the new API with exact-version Javadoc/sources before editing code. Update configurers/filters for MockMvc, WebTestClient, or REST Assured while preserving assertions, document identifiers, descriptors, and preprocessing rules. Finally, run tests, generate snippets into a clean output directory, compare contents, and render documentation. Migration is complete when both HTTP tests and the documentation pipeline operate cleanly on the new API.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs API Javadoc](https://docs.spring.io/spring-restdocs/docs/current/api/), [Spring REST Docs Releases](https://github.com/spring-projects/spring-restdocs/releases), [MockMvcRestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html), [WebTestClient integration reference](https://docs.spring.io/spring-restdocs/reference/), and [REST Assured Usage Guide](https://github.com/rest-assured/rest-assured/wiki/Usage).
