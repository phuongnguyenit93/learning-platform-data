# Ensuring Documentation Tasks Depend on Test Tasks

Spring REST Docs generates snippets only when an HTTP test actually executes the documentation step. Asciidoctor can render source files, yet if the rendering step runs before tests or is not wired to tests, include directives will fail to find files or silently read stale snippets left over from a previous build. In Maven, you must establish an explicit order: **run the snippet-generating tests first, then compile the documentation**.

This lesson belongs to the **Project Setup** chapter of the `SPRING_REST_DOCS` module. The module practices generating verifiable REST API documentation with Spring REST Docs from tests using MockMvc, WebTestClient, or REST Assured, producing snippets for requests, responses, payloads, parameters, and headers, then compiling Asciidoctor/Markdown in builds and CI. This lesson focuses on task dependencies across the Maven lifecycle, distinguishing Surefire from Failsafe, controlling direct goal invocations, profiles, and stale outputs.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why the Asciidoctor task must run after tests that generate snippets.
2. Read the Maven lifecycle and choose the right phase for plugin executions.
3. Configure `asciidoctor-maven-plugin` to run in a lifecycle where tests run beforehand.
4. Distinguish Surefire from Failsafe and pick the right documentation-generating suite.
5. Recognize why invoking a plugin goal directly or skipping tests can yield missing or stale docs.
6. Design profiles, multi-module builds, and CI to preserve the test → snippets → render order.
7. Diagnose include errors and verify builds from a clean state.

## 2. Why Is a Dependency Needed Between Testing and Rendering?

Spring REST Docs does not generate snippets by scanning source code. Tests execute requests, receive responses, verify results, and call `document(...)`. Only then are snippets written. Asciidoctor reads those files while resolving `include` directives.

```text
Source code + HTTP documentation tests
                 │
                 ▼
          Maven test lifecycle
                 │
                 ▼
       Surefire runs documentation tests
                 │
                 ▼
       Spring REST Docs writes operations
                 │
                 ▼
       target/generated-snippets/
                 │
                 ▼
       asciidoctor-maven-plugin
                 │
                 ▼
       Resolve include:: and render
                 │
                 ▼
       target/generated-docs/
```

If Asciidoctor runs before the snippet directory is created, an include such as:

```asciidoc
include::{snippets}/orders-get-success/http-response.adoc[]
```

cannot find the file. If the directory still holds snippets from an earlier build, the page may compile successfully while displaying outdated examples from a previous run. This is a subtle bug because the output looks valid on the surface.

A proper dependency must guarantee **the exact test suite producing the data runs before the rendering task consumes it**, not merely that both tasks happen to appear somewhere in the POM.

## 3. Maven Lifecycle and Phase Ordering

The Maven default lifecycle has these main phases:

| Phase | Role |
| --- | --- |
| `validate` | Validate the project is correct |
| `compile` | Compile main source code |
| `test-compile` | Compile test source code |
| `test` | Run unit tests via Surefire as configured |
| `prepare-package` | Prepare before packaging |
| `package` | Package the JAR/WAR artifact |
| `integration-test` | Run configured integration tests |
| `verify` | Run additional checks to verify the package meets criteria |
| `install` | Install the artifact into the local repository |
| `deploy` | Deploy the artifact to a remote repository |

When you invoke a phase, Maven executes all preceding phases in the same lifecycle. For example, `mvn package` runs `test`, `prepare-package`, and then `package`. Therefore, if Asciidoctor is bound to `prepare-package`, Surefire tests in the `test` phase run beforehand within the same invocation.

### 3.1. Choosing a Phase for Asciidoctor

Common execution configuration:

```xml
<execution>
    <id>generate-api-docs</id>
    <phase>prepare-package</phase>
    <goals>
        <goal>process-asciidoc</goal>
    </goals>
</execution>
```

This works when documentation tests run via Surefire in the `test` phase. By the time the build reaches `prepare-package`, tests have executed and snippets are ready.

Binding to a phase does not by itself guarantee tests generated snippets. Any of these cases can still leave data missing:

- `-DskipTests` is passed or Surefire is configured to skip tests.
- Test class names do not match naming/include patterns.
- Documentation tests only run inside an inactive profile.
- Snippet-generating tests run in Failsafe's `integration-test` phase, which executes after `prepare-package`.
- Tests do not configure Spring REST Docs or never call `document(...)`.

Therefore, before choosing a phase, verify which test suite actually produces the snippets.

## 4. Configuring Surefire and `asciidoctor-maven-plugin`

The following example uses JUnit 5, MockMvc, and documentation tests running in the `test` phase. Versions shown are illustrative; projects must pick versions compatible with their Spring Boot/Spring Framework, Java, and plugin setup.

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <spring-restdocs.version>3.0.3</spring-restdocs.version>
    <asciidoctor.maven.plugin.version>2.2.6</asciidoctor.maven.plugin.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <version>${spring-restdocs.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.2.5</version>
        </plugin>

        <plugin>
            <groupId>org.asciidoctor</groupId>
            <artifactId>asciidoctor-maven-plugin</artifactId>
            <version>${asciidoctor.maven.plugin.version}</version>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.restdocs</groupId>
                    <artifactId>spring-restdocs-asciidoctor</artifactId>
                    <version>${spring-restdocs.version}</version>
                </dependency>
            </dependencies>
            <executions>
                <execution>
                    <id>render-api-docs</id>
                    <phase>prepare-package</phase>
                    <goals>
                        <goal>process-asciidoc</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <sourceDirectory>
                    ${project.basedir}/src/docs/asciidoc
                </sourceDirectory>
                <outputDirectory>
                    ${project.build.directory}/generated-docs
                </outputDirectory>
                <backend>html</backend>
                <attributes>
                    <snippets>
                        ${project.build.directory}/generated-snippets
                    </snippets>
                </attributes>
            </configuration>
        </plugin>
    </plugins>
</build>
```

`spring-restdocs-mockmvc` lives in project dependencies with `test` scope. `spring-restdocs-asciidoctor` lives inside the plugin configuration because it supports Asciidoctor integration. The two dependencies do not replace each other.

### 4.1. Tests Must Actually Generate Snippets

Minimal MockMvc example:

```java
@ExtendWith(RestDocumentationExtension.class)
class ProductDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new ProductController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    @Test
    void getProduct() throws Exception {
        mockMvc.perform(
                RestDocumentationRequestBuilders
                    .get("/api/products/{id}", 7L)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andDo(document("products-get-success"));
    }
}
```

This example omits imports and descriptors to stay focused on task dependencies. In a real project, add assertions and descriptors for path/query parameters, headers, and payloads per the API contract. When the test runs, output may include:

```text
target/generated-snippets/products-get-success/
    http-request.adoc
    http-response.adoc
    curl-request.adoc
```

Field/parameter tables are generated only when the test declares the corresponding descriptors. Do not assume every operation produces every snippet type.

### 4.2. Verifying Surefire Discovers the Tests

Surefire runs only tests discovered according to its provider, naming conventions, include/exclude filters, and active profiles. If a documentation test class does not match the pattern, Maven can advance to `prepare-package` without generating any snippets.

Inspect reports in `target/surefire-reports` and Maven logs to confirm the expected classes and test counts ran. An exit code of `0` alone is insufficient: a build that discovers zero tests can still succeed unless additional checks are enforced.

## 5. Distinguishing Surefire and Failsafe

A project may generate snippets from unit/MVC tests or from integration tests that start a server and call endpoints over HTTP. Those two approaches execute in different phases.

| Plugin | Typical Phase | Purpose |
| --- | --- | --- |
| Maven Surefire | `test` | Runs unit tests and tests assigned to this suite |
| Maven Failsafe | `integration-test` and `verify` | Runs integration tests and verifies suite results |

Failsafe normally uses its `integration-test` goal to execute tests and its `verify` goal to check outcomes. If integration tests generate snippets, Asciidoctor must run after that suite finishes executing.

### 5.1. Snippets from Surefire

You can bind rendering to `prepare-package` if documentation tests run during `test` and serve as the required snippet source:

```text
test (Surefire)
    │
    ▼
generated-snippets
    │
    ▼
prepare-package (Asciidoctor)
    │
    ▼
package
    │
    ▼
verify
```

`mvn clean verify` executes all preceding phases in the default lifecycle, so Surefire tests in `test` run before `prepare-package`.

### 5.2. Snippets from Failsafe

If snippets are generated only during `integration-test`, binding Asciidoctor to `prepare-package` runs too early. You can move the render execution to `verify`:

```xml
<execution>
    <id>render-api-docs-after-integration-tests</id>
    <phase>verify</phase>
    <goals>
        <goal>process-asciidoc</goal>
    </goals>
</execution>
```

Verify the execution order within the `verify` phase using the effective POM and Maven logs: Failsafe tests must execute before Asciidoctor reads snippets, and Failsafe results must be verified per lifecycle rules. If ordering within the same phase is unclear, use a later phase/step or split documentation compilation into a dedicated step after the integration-test suite finishes.

**Never bind Asciidoctor to `prepare-package` if snippets are produced only in `integration-test`.**

## 6. Direct Goal Execution Does Not Run Test Phases

A common mistake is running:

```bash
mvn asciidoctor:process-asciidoc
```

This invokes the plugin goal directly. By default, it does not run the lifecycle phases preceding `prepare-package`. If tests have not run, snippets do not exist; if stale outputs remain, the plugin can render outdated data.

| Command | Relevant Behavior |
| --- | --- |
| `mvn test` | Runs lifecycle through `test`; does not execute goals bound to `prepare-package` |
| `mvn package` | Runs `test`, then `prepare-package` and `package` |
| `mvn verify` | Runs lifecycle through `verify` |
| `mvn clean verify` | Cleans build outputs, then runs lifecycle through `verify` |
| `mvn asciidoctor:process-asciidoc` | Invokes goal directly; does not automatically run Surefire first |
| `mvn -DskipTests package` | Skips test execution |
| `mvn -Dmaven.test.skip=true package` | Skips both test compilation and execution |

In release pipelines, prefer configured lifecycle commands like `mvn clean verify`. Run the goal directly only during local prose editing once snippets have already been generated and verified against the current source.

### 6.1. Profiles Can Break the Dependency Chain

If documentation tests or the Asciidoctor plugin live inside a Maven profile, CI must activate the right profile. Example:

```bash
mvn clean verify -Papi-docs
```

Check both sides: does the profile enable the snippet-generating tests, and does it enable the rendering plugin? If only one side is active, the task chain breaks. Normal builds without the profile active may produce no HTML or no fresh snippets.

### 6.2. Skipping Tests Conflicts with Generating Verifiable Docs

Skip flags allow a build to proceed without running documentation tests. If a job is responsible for producing verified documentation, never configure test skipping as the default. If you need fast artifact builds without docs, separate profiles or jobs explicitly and never treat such output as verified documentation from the current build.

## 7. Preventing Stale Outputs from Masking Failures

Snippets inside `target` are generated outputs. When tests are skipped or an operation identifier is renamed, files from a prior run can linger. Asciidoctor finds those files and compiles cleanly even though the current build's tests did not produce them.

How to prevent this:

1. Run `mvn clean verify` in CI to wipe `target` and rebuild from scratch.
2. Never track generated snippets as source files under `src`.
3. Ensure the render task runs after the snippet-generating suite.
4. Check Surefire/Failsafe test reports, not just the exit code.
5. Verify required identifiers/files before rendering if your pipeline has a separate verification step.
6. Never use test-skipping profiles in documentation-building jobs.

The Maven Clean Plugin can clear specific generated directories if a project needs to preserve certain other outputs. Normally, however, `mvn clean` deletes the entire `target` directory. Never keep the sole copy of AsciiDoc source files inside `target`, because it will be wiped.

## 8. Multiple Suites and Multi-Module Maven Builds

### 8.1. Multiple Test Suites Generating Snippets

If both MVC tests and integration tests generate snippets, separate their output directories or operation identifiers. Never let two suites write different content into the same operation folder.

```text
target/
├── generated-snippets-mvc/
│   ├── products-get-success/
│   └── orders-get-success/
├── generated-snippets-integration/
│   ├── products-get-database/
│   └── orders-get-authorization/
└── generated-docs/
```

Configure a dedicated output directory per suite; Asciidoctor must run after all suites whose snippets are referenced by the docs. You can declare matching attributes in the source document. This is a project organization strategy, not automatic behavior in Spring REST Docs.

### 8.2. Multi-Module Builds

In a multi-module Maven build, an API module may generate snippets while a docs module compiles AsciiDoc. Because the two modules have separate `target` directories, the docs module cannot automatically read the API module's snippets using a single common relative path.

Common options:

- Package snippets into an intermediate artifact and have the docs module depend on it.
- Copy snippet outputs between modules via an explicit build step.
- Use an explicitly configured shared output directory while carefully controlling parallel builds.

Example:

```text
parent
├── api-service
│   └── documentation tests → snippets
└── api-docs
    └── asciidoctor-maven-plugin → HTML
```

Keep dependencies one-directional: the API module produces outputs; the docs module consumes those generated outputs. Avoid circular dependencies where the API module needs documentation in order to build.

## 9. Verifying Execution Order

When suspecting Asciidoctor is running before tests, run:

```bash
mvn clean verify
```

Locate the Surefire/Failsafe logs and the `asciidoctor-maven-plugin:process-asciidoc` logs. Confirm the snippet-generating test suite finished before the plugin began rendering.

Use the effective POM to inspect configuration after Maven merges parent POMs and profiles:

```bash
mvn help:effective-pom
```

Check executions, phases, profiles, skip flags, plugin order, and output directories. For deeper detail, run `mvn -X clean verify`; debug logs are verbose and can expose paths or environment data, so review them before sharing.

## 10. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Include missing file | Render ran before tests or descriptor did not generate file | Check phase, tests, and descriptors |
| Page shows outdated examples | Leftover snippets from a previous build exist | Clean outputs and rerun tests |
| `mvn test` creates snippets but no HTML | Asciidoctor is bound to a phase after `test` | Run `package`/`verify` or the render phase |
| No integration snippets | Failsafe did not run or render ran before `integration-test` | Check Failsafe execution and move rendering later |
| Direct goal fails after `clean` | Direct goal does not run tests first | Use a lifecycle command |
| CI misses several pages | Profile/suite did not run | Check active profiles and test reports |
| Tests pass but response fields are missing | Descriptor omits required fields or uses relaxed mode | Cross-check contract and descriptors |
| Multi-module build cannot find files | Pointing to the wrong module's `target` | Copy or publish outputs explicitly |
| Tests skipped yet build passes green | Skip flags or Surefire configuration | Never skip tests in documentation jobs |
| Two suites overwrite snippets | Duplicate identifier in shared output directory | Separate identifiers or output directories |

### 10.1. Procedure for Investigating Missing Includes

1. Inspect reports to confirm the documentation tests actually ran.
2. Check `target/generated-snippets/<operation-id>/`.
3. Verify the included file is produced by the corresponding descriptor.
4. Compare the `snippets` attribute against the test output directory.
5. Check logs to confirm rendering ran after tests.
6. Run `mvn clean verify` to rule out stale outputs.
7. If it fails only in CI, check profiles, JDK, reactor modules, and skip flags.

## 11. Best Practices

- Bind rendering after the exact test suite that generates the snippets.
- Surefire in the `test` phase pairs cleanly with Asciidoctor in `prepare-package`.
- If snippets come from Failsafe integration tests, schedule rendering after the integration suite.
- Use lifecycle commands in CI instead of invoking the render goal standalone.
- Never use test-skipping flags in jobs responsible for generating documentation.
- Check test counts and reports to verify tests were actually discovered.
- Clean generated outputs to avoid stale snippets.
- Keep AsciiDoc sources outside `target`.
- Inspect the effective POM and logs whenever execution order is unclear.
- Separate output directories when multiple suites have independent lifecycles and content.

## 12. Practice Exercise

Create a Maven project using MockMvc to generate snippets for `GET /api/products/{id}`. The AsciiDoc page includes `http-request.adoc`, `http-response.adoc`, and `response-fields.adoc`.

**Tasks:**

1. Add `spring-restdocs-mockmvc` with `test` scope.
2. Configure `RestDocumentationExtension` and `document("products-get-success", ...)`.
3. Set snippet output to `target/generated-snippets`.
4. Bind `asciidoctor-maven-plugin` to `prepare-package`.
5. Run `mvn clean verify` and trace Surefire → snippets → Asciidoctor.
6. Confirm HTML is generated under `target/generated-docs`.
7. Run `mvn clean` and then invoke `mvn asciidoctor:process-asciidoc` directly; observe missing snippets when tests have not run.
8. Rerun `mvn clean verify` and confirm the page renders completely.
9. Try `-DskipTests` and explain why the build no longer guarantees fresh snippets.
10. Convert the test into a Failsafe integration test, pick an appropriate render phase, and verify the execution order in the logs.

**Completion criteria:** A clean build runs snippet-generating tests before rendering; include paths resolve correctly; tasks never consume stale outputs; when skipping or switching test suites, dependency issues are caught and handled intentionally.

## 13. Key Takeaways

- Spring REST Docs generates snippets only when tests execute and invoke the operation documentation step.
- Surefire tests in the `test` phase can generate snippets before Asciidoctor runs in `prepare-package`.
- If snippets come from Failsafe integration tests, rendering must run after that suite; `prepare-package` is normally too early.
- Invoking `asciidoctor:process-asciidoc` directly does not run preceding test phases automatically.
- `mvn clean verify`, test reports, effective POM, and execution logs verify the build order.
- Proper task dependencies ensure the right suite produces complete snippets before rendering, preventing stale outputs and keeping CI reproducible.
