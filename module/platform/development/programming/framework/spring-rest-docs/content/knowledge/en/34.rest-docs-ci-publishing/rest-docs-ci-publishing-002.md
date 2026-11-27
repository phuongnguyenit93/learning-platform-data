# Running Asciidoctor After Tests Complete

Spring REST Docs generates snippets when documentation tests execute requests, verify responses, and call the document API. Asciidoctor uses these snippets to compile the documentation pages. Therefore, **tests must complete successfully and generate all required snippets before Asciidoctor begins rendering**.

If Asciidoctor runs before tests, includes may fail to find files. If the output directory still holds snippets from an old build, rendering may sometimes succeed, yet the documentation will fail to reflect the current code. Build configuration must express clear dependencies, use a shared output directory, and propagate test failures to the render/publish step.

This lesson belongs to the **CI and Publishing** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generates snippets for requests, responses, payloads, parameters, and headers, and then compiles Asciidoctor/Markdown and integrates it into the build and CI.

## 1. Learning Objectives

After this lesson, you can:

1. Explain why Asciidoctor must run after documentation tests.
2. Set up dependencies between the test task and the Asciidoctor task in Gradle.
3. Bind the Asciidoctor execution into the Maven lifecycle after the test phase.
4. Configure a unified snippets directory between the test recorder and the renderer.
5. Clean old output and verify snippets are generated in the current build.
6. Ensure test failures prevent rendering and publishing.
7. Inspect the final artifacts to avoid missing or stale documentation.

## 2. Relationship Between Documentation Tests and Asciidoctor

Documentation tests perform HTTP exchanges and write snippets into the output directory. Asciidoctor reads these files via include directives. The proper flow:

```text
Compile test sources
       │
       ▼
Run documentation tests
       │
       ├── Failure ──► Stop build
       │
       ▼
Generate request/response snippets
       │
       ▼
Validate snippet inputs
       │
       ▼
Run Asciidoctor
       │
       ▼
Generate HTML/PDF documentation
       │
       ▼
Archive or publish
```

Asciidoctor does not automatically execute documentation tests just because an AsciiDoc page includes snippets. The build tool must be configured so the render task depends on the test task that generates those files.

### 2.1. Why Can Running Asciidoctor Alone Fail?

If you invoke the Asciidoctor task directly without a dependency, generated snippets may not yet exist in a clean checkout; includes may point to identifiers not created by tests; stale snippets may cause rendering to use outdated content; and documentation is not re-verified when tests or contracts change.

## 3. Unifying the Snippets Directory

Some common conventions:

```text
Gradle:
build/generated-snippets/

Maven:
target/generated-snippets/
```

The paths above are not mandatory. Choose a consistent output directory and configure both the test recorder and the Asciidoctor plugin to use that same value.

Test example:

```java
.andDo(document("orders-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Media type accepted by the client")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Order ID")
    )
));
```

The identifier `orders-get` creates the subdirectory containing the operation's snippets. AsciiDoc includes from that exact directory:

```asciidoc
=== Request

include::{snippets}/orders-get/http-request.adoc[]

=== Response

include::{snippets}/orders-get/http-response.adoc[]
```

If tests write to build/generated-snippets while Asciidoctor looks in target/generated-snippets, the build will report missing snippets even though tests ran.

## 4. Running Asciidoctor After Tests with Gradle

In Gradle, declare that the Asciidoctor task depends on the snippet-generating test task. General example:

```groovy
tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(layout.buildDirectory.dir("generated-snippets"))

    attributes(
        "snippets": layout.buildDirectory
            .dir("generated-snippets")
            .get()
            .asFile
            .absolutePath
    )
}
```

The example assumes the test task writes snippets to build/generated-snippets. Attribute syntax may vary by plugin version; check the DSL for the version declared in your project.

### 4.1. When Documentation Tests Have a Dedicated Task

Some projects separate unit tests and documentation tests:

```groovy
tasks.named("asciidoctor") {
    dependsOn(tasks.named("docsTest"))
    inputs.dir(layout.buildDirectory.dir("generated-snippets"))
}
```

The name docsTest is only an example; the actual task depends on the build script. This task must run the tests containing document(...). If Asciidoctor requires both unit tests and documentation tests, you can create a composite lifecycle task:

```groovy
tasks.register("prepareRestDocs") {
    dependsOn(tasks.named("test"))
    dependsOn(tasks.named("docsTest"))
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("prepareRestDocs"))
}
```

Use this structure only if those tasks exist. Do not add assumed task names without declaring them.

### 4.2. Running from the Command Line

Once dependencies are configured:

```bash
./gradlew clean asciidoctor
```

Gradle runs dependent tasks before Asciidoctor. You can invoke a composite task such as build if the project has already wired documentation into the lifecycle. Do not rely on typing multiple tasks in order on the command line instead of declaring dependencies in the build script.

## 5. Running Asciidoctor After Tests with Maven

Maven executes plugin goals according to lifecycle phases. Documentation tests typically run in the test (Surefire) or integration-test (Failsafe) phase, while Asciidoctor must be bound to a phase after the snippet-generating test group has completed.

Example when documentation tests run in Surefire:

```xml
<plugin>
  <groupId>org.asciidoctor</groupId>
  <artifactId>asciidoctor-maven-plugin</artifactId>
  <executions>
    <execution>
      <id>render-rest-docs</id>
      <phase>prepare-package</phase>
      <goals>
        <goal>process-asciidoc</goal>
      </goals>
      <configuration>
        <attributes>
          <snippets>${project.build.directory}/generated-snippets</snippets>
        </attributes>
      </configuration>
    </execution>
  </executions>
</plugin>
```

This is an illustrative structure; plugin version, goal, phase, and output need to match the project. The prepare-package phase occurs after test, so it works well if snippets are generated in the test phase.

### 5.1. When Documentation Tests Run via Failsafe

If integration/documentation tests are executed by Failsafe in integration-test and verify, Asciidoctor must not be placed in prepare-package because that phase comes before integration-test. Bind rendering to a phase after Failsafe completes, such as an appropriate execution in verify, or design a separate lifecycle that guarantees ordering.

What needs verification is that the render task runs only after snippet-generating tests succeed. Do not choose a phase merely because its name sounds fitting; check the actual lifecycle of the test plugin.

### 5.2. Maven Command

With tests configured in Surefire and Asciidoctor bound after the test phase:

```bash
./mvnw clean verify
```

With Failsafe, verify is the phase commonly used to finish integration tests and check results. Ensure the Asciidoctor execution runs after the test-verification goal, not merely after tests start.

## 6. Configuring the snippets Attribute in AsciiDoc

A document can declare an attribute:

```asciidoc
:snippets: build/generated-snippets

= Orders API

== Get order

=== Request

include::{snippets}/orders-get/http-request.adoc[]

=== Response

include::{snippets}/orders-get/http-response.adoc[]
```

In CI, attributes passed from the build plugin are usually easier to manage. Avoid defining separate snippets directories in tests, plugins, and AsciiDoc files without a single unified configuration source.

When using Maven, output usually lives under target; when using Gradle, usually under build. The attribute must match the output of the build tool being run.

### 6.1. Checking Include Identifiers

The identifier in document("orders-get", ...) must match the path in the include. When changing an identifier in a test, update the corresponding include. Missing files usually indicate that the test has not generated the snippet, the identifier has drifted, or the descriptor did not generate the included file.

## 7. Cleaning Output Before Tests

Stale snippets can hide unexecuted tests or removed operations. For example, a test previously generated orders-delete, and later the test was renamed or deleted; without cleaning, the old directory can remain and Asciidoctor will continue including it.

Use a clean build:

```bash
./gradlew clean asciidoctor
```

Or:

```bash
./mvnw clean verify
```

Clean deletes generated output; tests regenerate snippets; rendering uses fresh output. If the pipeline splits jobs, snippet artifacts must be generated from the exact same commit and never mixed with output from a previous build.

### 7.1. Do Not Treat Cached Snippets as Source of Truth

Dependency caching saves time resolving libraries. Generated snippets are test output and must be regenerated or passed as artifacts with clear provenance. Do not let the renderer silently use old cached snippets when tests did not run.

## 8. Ensuring Test Failures Stop Asciidoctor

The build tool must propagate documentation test failures to the render task:

- Gradle: a failed test task must fail dependent tasks; do not enable ignoreFailures for the publish pipeline.
- Maven Surefire/Failsafe: test failures must halt the lifecycle or mark the build failed; do not configure error-ignoring flags in the release job.
- CI: do not use continue-on-error for the snippet-generating test step or mandatory render steps.

If some non-documentation tests are allowed to run separately, group them clearly. The task that Asciidoctor depends on must include all documentation tests required to generate snippets.

### 8.1. Skipped Tests Are Not Passing Tests

A task with exit code 0 but a test count of 0 still generates no snippets. Check test reports and the number of executed tests. When publishing documentation, validation should confirm that required operations produced output.

## 9. Checks Before and After Rendering

Before Asciidoctor, verify the snippet directory contains the included files. After rendering, verify HTML/PDF files are freshly created.

Pre-render checklist:

- Documentation tests actually ran.
- Test reports contain no failures or unexpected skips.
- The snippets directory exists.
- Identifiers and included files are all present.
- Files are non-empty and belong to the current build.

Post-render checklist:

- HTML/PDF carries the current build identity.
- No content remains from stale snippets.
- Request/response sections render properly.
- No secrets or unpublishable fixture data are present.
- Artifacts are tied to the right commit.

You can create a verifyDocs task or a separate validation script. That task should fail with a specific message if files are missing.

## 10. Example Composite Task in Gradle

You can create a composite task invoked by both developers and CI:

```groovy
tasks.register("restDocs") {
    dependsOn(tasks.named("test"))
    dependsOn(tasks.named("asciidoctor"))
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
}
```

This is an example. If the project uses docsTest, swap the dependency accordingly and ensure asciidoctor also depends on the snippet-generating task. Avoid dependency cycles; tests must not depend back on restDocs.

Command:

```bash
./gradlew clean restDocs
```

Clean ensures old output is removed before test and render tasks run along the dependency graph.

## 11. General Lifecycle Example in Maven

With Maven, a straightforward approach is binding Asciidoctor to a phase after tests finish:

```text
validate
   │
compile
   │
test
   │
prepare-package
   │
Asciidoctor render
   │
package
   │
verify
```

This is a simplified diagram for the case where documentation tests run in the test phase. If using Failsafe, the diagram must reflect integration-test and verify; move Asciidoctor to a position after those phases. The exact lifecycle also depends on the project's execution/plugin bindings.

## 12. Common Errors and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Asciidoctor reports include file does not exist | Tests did not run or wrong identifier | Add dependency and check include path |
| Render succeeds but uses old snippets | Generated output not cleaned | Clean before tests |
| Running Gradle asciidoctor alone skips tests | Missing dependsOn | Declare dependency on render task |
| Maven renders before integration tests | Plugin bound to too early a phase | Move execution after Failsafe |
| Test task runs but produces no snippets | Tests filtered/skipped or missing document call | Check test report and operations |
| Works locally, CI fails on include | Different snippets directories | Use one shared property/attribute |
| Tests fail yet documentation still publishes | Failures ignored or continue-on-error set | Remove error-ignoring configuration |
| Snippet directory non-empty after clean | Output outside build/target or clean misses it | Locate output directory and clean the right path |
| HTML contains stale content | Render uses old output or did not rerun | Clean, test, and render in the same lifecycle |
| Include response-fields missing | Descriptor did not generate that file | Fix descriptor or include the right file |

## 13. Hands-On Exercise

Integrate the orders API documentation with Gradle or Maven. Documentation tests generate snippets for GET order; AsciiDoc includes request, response, headers, and fields.

**Tasks:**

1. Identify the test task that actually generates snippets.
2. Configure Asciidoctor to depend on that task.
3. Choose a single snippets directory and use the same value in both recorder and renderer.
4. Configure cleaning output before tests.
5. If using Maven Failsafe, place Asciidoctor after integration tests complete.
6. Verify that test failures stop rendering/publishing.
7. Check that every included identifier/file exists before rendering.
8. Render HTML/PDF from the current build's snippets.
9. Verify test reports, snippets, and artifacts belong to the same commit.
10. Run the build from a clean state and confirm task ordering is correct.

**Completion criteria:** Asciidoctor does not run before documentation tests; the snippets directory is unified; failing tests or missing snippets fail the build; documentation renders from fresh output without using stale files.

## 14. Key Takeaways

- Documentation tests generate snippets; Asciidoctor reads and renders snippets. Tests must run before rendering.
- Gradle needs declared task dependencies, typically via dependsOn.
- Maven needs Asciidoctor bound to a phase after documentation tests execute; note the difference between Surefire and Failsafe.
- Recorder and renderer must share the same snippets directory.
- Clean output before tests so stale snippets do not hide ungenerated operations.
- Test failures, unexpected skipped tests, or missing snippets must block documentation publishing.
- Check includes before rendering and HTML/PDF after rendering.
- Reproducible builds require running tests and rendering from the same source revision with consistent output provenance.
