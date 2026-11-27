# No Snippets Generated Because Tests Do Not Run

## 1. Symptoms and Diagnostic Principles

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Snippets are written only when a test actually reaches the Spring REST Docs integration, executes the request, and invokes the corresponding `document(...)` call or filter. If the tests are not discovered, are skipped, do not belong to the currently running task or lifecycle, or are excluded by a filter, the generated snippets directory will contain no new output.

Common symptoms:

- The build succeeds, but `build/generated-snippets` or `target/generated-snippets` does not appear.
- The snippets directory exists, but the expected operation directory is missing.
- Asciidoctor reports `include file not found`, or the operation macro has no content.
- Running tests from the IDE produces snippets, whereas running the build command or CI does not.
- The test report does not contain the REST Docs tests, or the tests are marked as skipped or ignored.

Key takeaway: **Asciidoctor does not run HTTP tests and does not generate snippets**. It only reads existing snippet files. Diagnose test discovery and the task/lifecycle first, and only then check the document filter and output path.

```mermaid
flowchart TD
    A[No new snippets] --> B[Check the test report]
    B --> C{Were tests discovered?}
    C -->|No| D[Check source set, class/method names, engine]
    C -->|Yes| E{Did tests execute?}
    E -->|Skipped| F[Check tags/filters/profiles/skip flags]
    E -->|Failed before document()| G[Read exception and setup]
    E -->|Passed| H[Check REST Docs filter and output path]
    D --> I[Re-run the exact test]
    F --> I
    G --> I
    H --> J[Check operation directory and snippet files]
    I --> B
```

## 2. Confirming Whether Tests Actually Ran

Do not start by editing Asciidoctor. First, open the test report or build log and look for the test class or method name that generates the snippets.

Questions to answer:

1. Is the test class located in a test source set recognized by the build tool?
2. Do the class and method names match the discovery rules of the test engine/plugin?
3. Is the test excluded by an include/exclude pattern, tag, group, profile, or property?
4. Did the test execute, or was it skipped/disabled/ignored?
5. Did the test fail during context initialization, dependency injection, or setup before sending the HTTP request?
6. Does the currently running task or lifecycle include the test source set or module containing the REST Docs tests?

A `BUILD SUCCESSFUL` or `BUILD SUCCESS` line does not prove that every intended test ran. A build can succeed when no tests are found, when tests are skipped, or when the module containing the tests is not part of the current lifecycle.

## 3. Checking Gradle: Source Sets, Tasks, and Test Discovery

With Gradle, regular Java tests reside in `src/test/java` and are executed by the `test` task. If the project uses a custom source set, integration tests may belong to another task such as `integrationTest` or `docsTest`.

Inspect the list of tasks:

```bash
./gradlew tasks --all
```

Run the test task with more detailed logging:

```bash
./gradlew test --info
```

Run a specific test class:

```bash
./gradlew test --tests "com.example.docs.BooksDocumentationTest"
```

If the tests reside in a separate integration task:

```bash
./gradlew integrationTest --info
```

The task name must be the actual task configured in the project. Do not assume `test` will execute tests belonging to a custom source set.

### Checking the Source Set

Standard layout:

```text
src/
├── main/java/...
└── test/java/
    └── com/example/docs/BooksDocumentationTest.java
```

If the file is located in `src/integrationTest/java`, a configured integration source set and task are required. If the file is mistakenly placed in `src/main/java`, it is not a regular test source.

Example declaration of an integration test source set (classpath/task configuration abbreviated):

```groovy
sourceSets {
    integrationTest {
        java.srcDir file('src/integrationTest/java')
        resources.srcDir file('src/integrationTest/resources')
        compileClasspath += sourceSets.main.output
        runtimeClasspath += output + compileClasspath
    }
}
```

Declaring a source set does not automatically guarantee that the task runs during `check` or before Asciidoctor. You must explicitly configure the corresponding task and build dependencies.

## 4. Checking the JUnit Test Engine and Test Naming

Tests may fail to be discovered if the test engine or naming convention does not match.

| Case | What to check |
| --- | --- |
| JUnit 5 | Is the JUnit Jupiter engine on the test runtime classpath, and is `useJUnitPlatform()` declared if required by the Gradle configuration? |
| JUnit 4 | Is a suitable JUnit 4 runner/provider present without mixing inconsistent engine configurations? |
| Test class not found | Does the class name match the include patterns of Gradle or Maven Surefire/Failsafe? |
| Method not executed | Does it have the `@Test` annotation, the right JUnit import, and no disabling condition skipping it? |
| Tests using `@Tag` | Does a tag filter exclude the documentation tag from the run? |
| Tests depending on profiles/properties | Do environment conditions cause the test to be disabled or fail an assumption? |

JUnit 5 example with Gradle:

```groovy
tasks.named('test') {
    useJUnitPlatform()
}
```

Example test:

```java
import org.junit.jupiter.api.Test;

class BooksDocumentationTest {

    @Test
    void documentGetBook() {
        // Send the request and invoke the Spring REST Docs document filter.
    }
}
```

Verify that you import `org.junit.jupiter.api.Test` if the project uses JUnit 5. A test using an annotation from another engine while the build only configures Jupiter may not be discovered as expected.

## 5. Checking Filters, Tags, and Skip Conditions in Gradle

Gradle can filter tests via `--tests`, test filters, tag expressions, task configuration, or conditional logic. For example:

```bash
./gradlew test --tests "com.example.service.*"
```

This command only runs classes matching the pattern. If the REST Docs tests are in another package, they will be excluded.

A JUnit 5 tag filter may be configured as:

```groovy
tasks.named('test') {
    useJUnitPlatform {
        includeTags 'unit'
    }
}
```

If REST Docs tests carry the `documentation` tag, a configuration that only includes `unit` will not run them. You can add the required tag or use a dedicated task for documentation tests:

```groovy
tasks.register('documentationTest', Test) {
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'documentation'
    }
}
```

This is a guiding example; if the `test` task also runs the same classes, avoid duplicate runs or configure distinct tags deliberately. Check `onlyIf`, `exclude`, `enabled`, `failOnNoMatchingTests`, and custom properties if the task is skipped.

## 6. Test Skip Flags and Build Profiles

Certain build commands can skip tests or only compile them:

| Command/configuration | Possible consequence |
| --- | --- |
| `-x test` (Gradle) | Skips the `test` task; snippets are not generated from that task. |
| `-DskipTests` (Maven Surefire convention) | Tests may be compiled but not executed. |
| `-Dmaven.test.skip=true` | May skip both compiling and running tests. |
| Inactive Maven profile | Plugin/test executions declared inside the profile may not run. |
| Gradle property controlling a task | The task may be disabled or skipped by project configuration. |
| `@Disabled`, `@Ignore`, assumptions | The test or method may not execute. |

If the goal is to generate documentation, do not use test-skipping flags in the snippet-generation job. A unit-test job may be optimized separately, but the documentation job must run the snippet-generating tests.

## 7. Checking Maven: Surefire, Failsafe, and Lifecycle

Maven commonly uses:

- **Surefire** to run unit tests in the `test` phase.
- **Failsafe** for integration tests in the `integration-test` and `verify` lifecycles.

If REST Docs tests belong to the integration test group but the build only invokes `mvn test`, Failsafe may not have run. In that case, use the appropriate lifecycle, typically:

```bash
mvn clean verify
```

Check the test reports:

```text
target/surefire-reports/
target/failsafe-reports/
```

The report directory name depends on plugin configuration, but these are the common defaults. Look for the REST Docs class in the report to see whether it was discovered, executed, skipped, or failed.

### Naming Conventions

Surefire and Failsafe have different default include patterns. For instance, `*Test` names are typically recognized by Surefire; `*IT` names are typically used for integration tests with Failsafe. If a class is named `BooksDocumentationIT` but only Surefire runs, the test may not be in the executed set. Check `<includes>`, `<excludes>`, and plugin execution configurations rather than renaming the class arbitrarily.

### Skip Properties

Check the CI command and POM for `skipTests`, `maven.test.skip`, or project-specific properties. If the profile containing the Failsafe execution is inactive, `mvn verify` will not run integration tests inside that profile either.

## 8. Verifying That the Task or Lifecycle Runs Before Asciidoctor

Another common mistake is that HTTP tests exist, but the build only invokes Asciidoctor. For example:

```bash
./gradlew asciidoctor
```

or only invoking the Maven documentation rendering goal. Without a task dependency or lifecycle phase ensuring tests run first, Asciidoctor may read an empty directory or stale snippets.

With Gradle, declare the dependency:

```groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
}
```

If snippets are generated by `integrationTest`, the dependency must point to the right task:

```groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('integrationTest')
}
```

With Maven, place the Asciidoctor execution in a phase after the snippet-generating tests and run the lifecycle up to that phase, such as `verify` if the tests are under Failsafe. If the test execution resides in a profile, activate that profile during the documentation build.

Do not just look at the ordering in the configuration file; inspect the task graph or build log to confirm the task was actually scheduled and executed.

## 9. If Tests Run but Snippets Are Still Missing

Once the test report confirms that the test ran and passed, move on to checking the Spring REST Docs integration:

1. Does the test make an actual request?
2. Is the REST Docs filter or extension attached to the request?
3. Does the test invoke `document("operation-id", ...)` properly?
4. Does the request reach the filter execution step before the test finishes?
5. Does the output directory used by the test match the location you are inspecting?
6. Does the test use an identifier different from the directory name you are looking for?

REST Assured example:

```java
given(this.specification)
        .filter(document("books-get"))
.when()
        .get("/api/books/42")
.then()
        .statusCode(200);
```

MockMvc example:

```java
mockMvc.perform(get("/api/books/{id}", 42))
        .andExpect(status().isOk())
        .andDo(document("books-get"));
```

WebTestClient example:

```java
webTestClient.get()
        .uri("/api/books/{id}", 42)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("books-get"));
```

These snippets are abbreviated examples; the test needs the corresponding REST Docs integration setup (REST Assured filter, MockMvc documentation configuration, or WebTestClient REST Docs filter) and static imports appropriate for your version. If the filter is not attached to the request, the test can pass without generating snippets.

## 10. Checking the Output Directory and Operation Identifier

Do not assume snippets live in only one fixed folder. Common conventions:

| Build tool | Common default output |
| --- | --- |
| Gradle | `build/generated-snippets/` |
| Maven | `target/generated-snippets/` |

A project may customize the output directory. Check the `outputDirectory` or snippets directory configuration in the REST Docs setup, then look for the exact operation identifier:

```text
generated-snippets/
└── books-get/
    ├── curl-request.adoc
    ├── http-request.adoc
    └── http-response.adoc
```

The `books-get` directory is determined by the identifier passed to `document("books-get", ...)`. If the test uses `books-get-200`, looking for `books-get/` will not find the output.

To avoid mistaking stale output for fresh output:

- Run `clean` before a diagnostic build.
- Check the timestamp of the operation directory.
- Do not manually edit generated snippets.
- Verify that Asciidoctor `{snippets}` points to the exact location where the tests write files.

## 11. Diagnosing from Test Reports and Build Logs

Read the results in order:

| Observed result | Initial conclusion | Next step |
| --- | --- | --- |
| Test class missing from report | Test was not discovered, or the module/task did not run. | Check source set, naming convention, include/exclude, and module selection. |
| Test has skipped status | A filter, tag, disabled condition, or skip property is active. | Inspect the log for the skip reason and corresponding configuration. |
| Test failed before HTTP request | Setup, context, or fixture error. | Fix the test failure before inspecting snippets. |
| Test passed, no operation folder | Filter/document call or output path is wrong. | Check the integration setup and identifier. |
| Snippets exist, Asciidoctor cannot find them | `{snippets}` or include path is wrong. | Align the output directory and attribute. |
| Present locally, missing in CI | Commands, profiles, environment, task graph, or cache differ. | Compare commands, properties, test reports, and build logs. |

For Gradle, you can use `--info` or `--debug` when more detail is needed, though `--debug` can produce large logs and expose environment information. Use it only when necessary and review logs before sharing.

## 12. End-to-End Troubleshooting Walkthrough

Suppose `BooksDocumentationTest` contains `document("books-get")`, yet after the build there is no `books-get/`.

**Step 1 — Run the exact test class:**

```bash
./gradlew test --tests "com.example.docs.BooksDocumentationTest" --info
```

If Gradle reports no matching tests or the report does not contain the class, check the package, source set, test engine, and class name.

**Step 2 — Check the test report:**

Confirm the method has a passed status rather than skipped. If it failed during Spring context or fixture setup, fix that issue first.

**Step 3 — Check the document integration:**

Verify that the test attaches the Spring REST Docs filter/configuration and that the request passes through the filter containing `document("books-get")`.

**Step 4 — Check the output:**

Locate `build/generated-snippets/books-get/` or the configured custom output directory. Confirm that new files were created.

**Step 5 — Run rendering:**

```bash
./gradlew clean test asciidoctor
```

If the snippets exist but the include fails, check the `{snippets}` attribute and filename in AsciiDoc. Do not keep modifying the test if the actual cause is just the include path.

## 13. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Green build with no snippets | Tests were not scheduled or were skipped. | Read the test report and check tasks/lifecycle and skip flags. |
| Test class not found | Wrong source set, naming pattern, or engine. | Put tests in the right source set and configure JUnit/Surefire/Failsafe properly. |
| Running `mvn test` skips `*IT` | Integration tests belong to a Failsafe execution. | Run the appropriate lifecycle such as `mvn verify` and activate required profiles. |
| `./gradlew asciidoctor` generates no snippets | Only the renderer ran, not the snippet-generating tests. | Add a task dependency or run `test`/integration task first. |
| Tests skipped in CI | `-x test`, `-DskipTests`, tag filter, or property. | Fix the command/profile/filter for the documentation job. |
| Tests pass but `document(...)` output is missing | Filter not attached or test uses another identifier. | Check setup and `document(...)` calls in the test. |
| Snippets appear in another directory | Output directory was customized. | Read the REST Docs configuration and align `{snippets}`. |
| Asciidoctor reports missing include | Test has not created the file or include filename is wrong. | Verify the output file first, then fix the include. |
| Passes locally, missing snippets in CI | CI runs a different task/profile or uses stale cache/output. | Compare build commands, test reports, profiles, and clean output. |

## 14. Practical Checklist

- [ ] Confirmed the test class/method appears in the test report.
- [ ] The test actually executed and was not skipped or disabled.
- [ ] Source set and Gradle task or Maven lifecycle are configured appropriately.
- [ ] JUnit engine and test naming conventions are configured properly.
- [ ] Tags, include/exclude patterns, profiles, and skip flags do not exclude documentation tests.
- [ ] Asciidoctor depends on the exact task that generates snippets.
- [ ] The test attaches the Spring REST Docs filter/extension and invokes `document(...)`.
- [ ] The output directory and operation identifier match the location being checked.
- [ ] Clean build does not rely on stale snippets.
- [ ] Asciidoctor runs only after snippet-generating tests pass.
- [ ] CI uses the same test/profile/task configuration as the intended documentation build.

When snippets are missing, verify that tests are discovered and executed before checking Asciidoctor. If tests do not run, the cause usually lies in the source set, test engine, naming convention, filter/tag, skip flag, or lifecycle. If tests already pass, continue checking the REST Docs filter, `document(...)`, operation identifier, and output directory. Layer-by-layer diagnosis pinpoints the exact break in the test -> snippet -> Asciidoctor pipeline.

## References

- [Spring REST Docs – Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Spring REST Docs – Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle – Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Maven Surefire Plugin – Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Maven Failsafe Plugin – Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
