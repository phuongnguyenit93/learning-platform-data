# Output Directory Not Found

## 1. Distinguishing the Snippets Directory from the Rendered Documentation Directory

Spring REST Docs creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. After tests execute through the REST Docs integration, the framework writes snippets such as `http-request.adoc`, `http-response.adoc`, `request-fields.adoc`, and `links.adoc` to an output directory. Asciidoctor reads these files to generate HTML/PDF into a different output directory.

Therefore, when encountering an "output directory not found" error, first determine **which directory is missing**:

| Directory | What does it contain? | Created by |
| --- | --- | --- |
| Generated snippets | `.adoc` files per operation, such as `books-get/http-response.adoc`. | Spring REST Docs while HTTP tests run. |
| Asciidoctor source | `index.adoc`, operation files, and prose written by the team. | Documentation authors / repository. |
| Rendered documentation | HTML, PDF, or DocBook. | Asciidoctor task/plugin. |

Common paths:

```text
Gradle:
  build/generated-snippets/       # Spring REST Docs snippets
  build/docs/asciidoc/html5/      # HTML output, depending on plugin configuration

Maven:
  target/generated-snippets/     # Spring REST Docs snippets
  target/generated-docs/         # Possible HTML output, depending on plugin configuration
```

These are common conventions, not mandatory paths. A project may configure different output directories. Do not conclude a directory is missing just because you checked the default path while the build is configured with a custom path.

## 2. Identifying Exactly Which Component Reports the Error

Read the error message and determine whether it comes from the tests, Spring REST Docs, or Asciidoctor:

| Symptom | Likely cause |
| --- | --- |
| Tests run but do not create `generated-snippets`. | Tests do not pass through the REST Docs filter, the output directory differs, or no operation was documented. |
| File/directory write error during tests. | Invalid path, write permissions, parent directory, or filesystem issue. |
| `include file not found`. | Asciidoctor cannot find the included snippet file; `{snippets}` may be wrong or tests have not generated the file. |
| `operation::...` has no content. | The operation ID does not exist in the snippets directory read by the extension. |
| HTML/PDF does not appear. | The Asciidoctor task/plugin did not run, the output path differs, or rendering failed. |

Do not manually create an empty directory to silence the error. Find out why the component responsible for writing the output failed to produce content.

## 3. Checking Where Spring REST Docs Writes Snippets

Locate the test REST Docs configuration and determine the output directory passed to the integration. Common configuration approaches:

- Spring Boot test annotation `@AutoConfigureRestDocs(outputDir = "...")`.
- JUnit `RestDocumentationExtension` with the appropriate output directory configuration.
- MockMvc `MockMvcRestDocumentation.documentationConfiguration(...)`.
- WebTestClient `WebTestClientRestDocumentation.documentationConfiguration(...)`.
- REST Assured `documentationConfiguration(restDocumentation)`.

Spring Boot with MockMvc example:

```java
@WebMvcTest(BookController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class BookDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getBook() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42))
                .andExpect(status().isOk())
                .andDo(document("books-get"));
    }
}
```

Example using `RestDocumentationExtension`:

```java
@ExtendWith(RestDocumentationExtension.class)
class BookDocumentationTest {

    @BeforeEach
    void setUp(WebApplicationContext context,
               RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

In the second example, the output directory is provided via `RestDocumentationContextProvider` and the extension configuration. If you need a custom path, configure the extension/provider according to your API and version; do not assume the Spring Boot annotation and the JUnit extension always pick the same path.

When using REST Assured or WebTestClient, you must also attach the corresponding filter to the request. If the filter or documentation configuration is not attached, the test may send HTTP requests successfully without producing snippets.

## 4. Aligning the Output Directory with Gradle

Gradle example using `build/generated-snippets`:

```groovy
plugins {
    id 'java'
    id 'org.asciidoctor.jvm.convert' version '3.3.2'
}

configurations {
    asciidoctorExt
}

def snippetsDir = layout.buildDirectory.dir('generated-snippets')

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

tasks.named('test') {
    outputs.dir snippetsDir
    useJUnitPlatform()
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    configurations 'asciidoctorExt'
    attributes 'snippets': snippetsDir.get().asFile
}
```

In the tests, the REST Docs configuration must write to the same `build/generated-snippets` directory. `outputs.dir` only declares the output for Gradle; it **does not configure Spring REST Docs to write there**. These are two separate configurations and must match.

If the tests are writing to `target/generated-snippets` or a custom folder, you have two choices: change the test output directory to follow the Gradle convention, or keep the test path and update `snippetsDir` and the Asciidoctor attribute accordingly. Avoid configuring each component with a different location.

## 5. Aligning the Output Directory with Maven

Maven conventions typically use `${project.build.directory}/generated-snippets`, corresponding to `target/generated-snippets`:

```xml
<properties>
    <restdocs.outputDir>${project.build.directory}/generated-snippets</restdocs.outputDir>
</properties>
```

With Spring Boot tests, you can use a property/annotation to set the output directory according to the project configuration:

```java
@AutoConfigureRestDocs(outputDir = "target/generated-snippets")
class BookDocumentationTest {
    // HTTP tests
}
```

The Asciidoctor Maven Plugin must use that exact directory:

```xml
<configuration>
    <attributes>
        <snippets>${project.build.directory}/generated-snippets</snippets>
    </attributes>
</configuration>
```

If the test module and documentation module are two separate Maven modules, `${project.build.directory}` resolves independently for each module. In that case, the docs module may look in `module-docs/target/generated-snippets` while tests write to `module-api/target/generated-snippets`. Configure cross-module paths explicitly or package snippets as an artifact consumed by the docs module.

## 6. Checking Paths in a Multi-Module Project

This is a common cause when running locally inside a module works, whereas CI runs from the root project.

Example:

```text
store-parent/
├── api-tests/
│   └── target/generated-snippets/
└── api-docs/
    ├── pom.xml
    └── target/generated-docs/
```

Tests in `api-tests` generate snippets in `api-tests/target/generated-snippets`. Asciidoctor running in `api-docs` will not automatically see that directory if its `snippets` attribute points to `api-docs/target/generated-snippets`.

Determine:

1. Which module contains the HTTP documentation tests?
2. Which module runs Asciidoctor?
3. Where do tests write snippets when executed from the reactor root?
4. By what path, copy task, or artifact dependency does the docs module receive snippets?
5. Does the build guarantee that the test module runs before the docs module?

Do not hard-code absolute paths from a developer's machine. Use paths relative to the project/module root or Maven/Gradle configurations reproducible in CI.

## 7. Checking Write Permissions and the Filesystem

If logs show directory creation or file write errors, check:

- Does the user running Gradle/Maven have write permission to the build directory?
- Is the workspace mounted read-only or locked by another process?
- Does the parent directory exist as a real directory, rather than a file with the same name?
- Does the disk have free space and quota remaining?
- Does the path contain invalid characters, wrong separators, or exceed length limits?
- Is the CI workspace cleaned up between the test run and Asciidoctor?

On Linux/macOS, you can check:

```bash
ls -ld build build/generated-snippets
test -w build && echo "build directory is writable"
```

On PowerShell:

```powershell
Get-Item .\build
Get-Item .\build\generated-snippets -ErrorAction SilentlyContinue
```

If the directory does not exist yet, `Get-Item` may report it is not found; that only confirms the path does not exist, not the root cause. Check test logs and workspace write permissions.

Do not grant broad permissions like `chmod -R 777` to work around an undiagnosed error. Fix ownership/permissions on the specific build directory for the CI user.

## 8. Distinguishing the Test Output Directory from the Asciidoctor Output Directory

These two settings are often confused:

```groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    outputDir = file("$buildDir/docs/asciidoc/html5")
}
```

`snippetsDir` is the input to Asciidoctor, whereas `outputDir` is where the rendered HTML is stored. Changing `outputDir` does not change where Spring REST Docs writes snippets. Conversely, changing the snippets directory does not automatically change where HTML is emitted.

The same applies to Maven: `target/generated-snippets` is the input, while the Asciidoctor Maven Plugin's output directory is the HTML/PDF output. When HTML is missing, inspect the render task/plugin. When includes are not found, inspect the snippets path first.

## 9. Running a Clean Build and Verifying Directories

To rule out stale output or unapplied configuration changes, run an appropriate clean build.

Gradle:

```bash
./gradlew clean test --info
```

After tests pass, verify:

```bash
find build/generated-snippets -maxdepth 2 -type f
```

Maven:

```bash
mvn clean test
```

After tests pass, verify:

```bash
find target/generated-snippets -maxdepth 2 -type f
```

The `find` commands are examples for Unix shells. On PowerShell, you can use:

```powershell
Get-ChildItem .\build\generated-snippets -Recurse -File
Get-ChildItem .\target\generated-snippets -Recurse -File
```

If the directory is still missing, check the test report and REST Docs filter. If the operation directory contains files but Asciidoctor cannot find them, check the `snippets` attribute and include paths.

## 10. Diagnosing by Symptom

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| No `generated-snippets` after tests | Tests did not run, filter not attached, or output path differs. | Check the test report, `document(...)`, REST Docs setup, and output directory. |
| `generated-snippets` exists, no operation folder | Different identifier, test did not reach document filter, or scenario did not run. | Compare `document("operation-id")` with the test report. |
| Operation folder exists, some files missing | Only certain descriptors/snippets were declared, or request did not reach filter. | Check `document(...)` and the actual content written by tests. |
| Snippets in module A, Asciidoctor looks in module B | Multi-module path is not shared. | Configure an artifact/copy path or cross-module attribute. |
| Include reports file does not exist | Wrong `snippets` attribute or wrong filename/operation ID. | Verify files on disk, then fix the include/attribute. |
| HTML/PDF not generated | Asciidoctor task/plugin did not run or rendering failed. | Check task lifecycle and the renderer's own output directory. |
| Access denied error | Workspace or parent directory denies user writes. | Fix permissions/ownership within the proper scope. |
| Output missing in CI but present locally | Relative paths, modules, users, cleanup, or task graphs differ. | Compare build commands, environment, and CI logs. |

## 11. End-to-End Troubleshooting Workflow

Suppose tests pass, yet `books-get/http-response.adoc` is not found:

1. Check the test report to confirm the exact test method ran and was not skipped.
2. Locate the `document("books-get", ...)` call and verify the filter/extension is attached to the request.
3. Inspect the Spring REST Docs output directory configuration (annotation, extension, or custom setup).
4. Run a clean test build and locate the operation directory in the actual output directory.
5. If files exist at path A while Asciidoctor reads path B, align `{snippets}` and the build configuration.
6. If files are not generated, read test logs for errors before or after the document filter executes.
7. If both tests and snippets are right, check the include filename, case sensitivity, and relative path.
8. Re-run Asciidoctor once the tests have successfully generated output.

Do not edit an include to point to a directory that happens to hold stale snippets. Make the test output directory and documentation input directory consistent and reproducible.

## 12. Common Errors

| Symptom | Cause | Direction to resolve |
| --- | --- | --- |
| Looking for `build/generated-snippets` and not finding it | Project uses a custom output or tests have not written snippets. | Check the REST Docs configuration and test report. |
| `outputs.dir` declared, directory still empty | Gradle output declaration does not configure the REST Docs writer. | Configure test integration to write to the right path. |
| Changed Asciidoctor `outputDir`, include still fails | Changed HTML output instead of snippets input. | Configure the `snippets` attribute separately. |
| Spring Boot and JUnit extension write to two places | Two test setups use different output configurations. | Standardize on a shared output directory. |
| Multi-module build looks in the wrong `target` | `${project.build.directory}` belongs to the current module. | Pass/copy snippets from the test module to the docs module. |
| Directory exists but is unwritable | Permissions, mount, or quota. | Check exact user and write permissions. |
| Old files let includes pass | Clean did not run or output was cached/copied over. | Clean the right module and verify timestamps/build identity. |
| CI path differs from local | Different working directory or module invocation. | Use project-relative configuration and run from the same entry point. |

## 13. Practical Checklist

- [ ] Determined whether the missing directory is the snippets directory or the rendered HTML/PDF directory.
- [ ] Test report confirms HTTP documentation tests ran.
- [ ] REST Docs filter/extension is attached to requests and calls `document(...)` with the right operation ID.
- [ ] Spring REST Docs output directory has been verified from the actual configuration.
- [ ] Gradle/Maven declares input/output properly without confusing task declarations with REST Docs writer configuration.
- [ ] Asciidoctor `{snippets}` points to the exact directory where tests write files.
- [ ] Multi-module builds share snippets properly between the test module and docs module.
- [ ] The build user has write permissions and sufficient disk space in the workspace.
- [ ] Clean build does not use stale snippets.
- [ ] Asciidoctor runs after tests and consumes snippets from the current build.

When an output directory is not found, separate where Spring REST Docs writes snippets from where Asciidoctor emits HTML/PDF. Then trace the configuration from test integration, output directory, and build tasks to `{snippets}` and include paths. In multi-module projects, clearly identify which module owns the output and how the documentation module consumes it. Aligning these paths and running a clean build makes the issue reproducible and fixes the true root cause.

## References

- [Spring REST Docs – Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Spring REST Docs – JUnit 5 Support](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Spring REST Docs – Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle – Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Maven – POM Reference: Build](https://maven.apache.org/pom.html#Build)
