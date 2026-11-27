# Packaging Generated Documentation into Artifacts

## 1. Purpose and Artifact Creation Flow

Spring REST Docs generates snippets from HTTP tests run with MockMvc, WebTestClient, or REST Assured. Snippets such as `http-request.adoc`, `http-response.adoc`, and `request-fields.adoc` are intermediate data. Asciidoctor combines them with source AsciiDoc documents to render HTML/PDF. The next packaging step places the rendered documentation into an artifact for CI storage, release pipeline publishing, or deployment to an internal website.

Typical flow:

~~~text
Source code + documentation tests
                |
                v
         Run HTTP tests
                |
                v
      generated-snippets/
                |
                v
      AsciiDoc + includes
                |
                v
           Asciidoctor
                |
                v
       Rendered HTML / PDF
                |
                v
       ZIP / JAR / PDF artifact
                |
                v
       CI artifact storage / release
~~~

In the **SPRING_REST_DOCS** module, REST API documentation must reflect verified requests/responses. Therefore, artifacts must be built from the same commit and the same test run of the build. Do not package stale snippets or documentation rendered from a workspace of unknown origin.

## 2. Choosing the Artifact Type

Before configuring the build, determine who will consume the artifact:

| Artifact type | Contents | Purpose |
| --- | --- | --- |
| HTML ZIP | Entire HTML website and accompanying assets | Upload to CI, download, or deploy to static hosting |
| PDF | Documentation rendered as PDF | Download, archive, or attach to releases |
| Snippets ZIP | Snippets organized by document identifier | Share with another docs module or integration team |
| AsciiDoc source bundle | AsciiDoc, includes, and required resources | Rebuild documentation in another environment |
| JAR classifier | HTML or documentation placed inside a JAR | Distribute via a Maven/Gradle repository |

Usually, API consumers need HTML/PDF. Snippets are better suited for development teams or documentation authoring pipelines. It is not necessary to publish every artifact type on every build.

An HTML artifact must contain all related files:

~~~text
api-docs/
├── index.html
├── css/
├── js/
├── images/
└── ...
~~~

Copying only index.html will lose CSS, images, or subpages. Package the entire Asciidoctor output directory.

## 3. Gradle: Creating a ZIP from Rendered Documentation

Assume the asciidoctor task renders documentation into build/docs/asciidoc. Create a ZIP task:

~~~groovy
def renderedDocs = layout.buildDirectory.dir('docs/asciidoc')

tasks.register('apiDocsZip', Zip) {
    dependsOn tasks.named('asciidoctor')
    from(renderedDocs)
    archiveBaseName = 'registration-api-docs'
    archiveClassifier = 'html'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

The apiDocsZip task depends on asciidoctor, so documentation is rendered before ZIP reads the output directory.

Run:

~~~bash
./gradlew clean apiDocsZip
~~~

The artifact is typically located under:

~~~text
build/distributions/
└── registration-api-docs-html.zip
~~~

The final filename also depends on the project version and archive naming convention. You can include the version:

~~~groovy
tasks.register('apiDocsZip', Zip) {
    dependsOn tasks.named('asciidoctor')
    from(renderedDocs)
    archiveBaseName = 'registration-api-docs'
    archiveVersion = project.version.toString()
    archiveClassifier = 'html'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

### 3.1. Wiring into the Build Lifecycle

If every build needs the documentation artifact, you can wire the task into assemble:

~~~groovy
tasks.named('assemble') {
    dependsOn tasks.named('apiDocsZip')
}
~~~

Then:

~~~bash
./gradlew clean build
~~~

will build both the application artifact and the docs artifact according to the dependency graph. If documentation is only needed in a release job, keep apiDocsZip as a separate task to avoid rendering docs on every local build.

### 3.2. Creating a Separate Snippets Artifact

If another module needs to include snippets, you can create a second ZIP:

~~~groovy
def snippetsDir = layout.buildDirectory.dir('generated-snippets')

tasks.register('apiSnippetsZip', Zip) {
    dependsOn tasks.named('test')
    from(snippetsDir)
    archiveBaseName = 'registration-api-snippets'
    archiveVersion = project.version.toString()
    archiveClassifier = 'snippets'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
~~~

Ensure both the test task and Spring REST Docs write to build/generated-snippets. Example:

~~~java
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
~~~

The snippets ZIP preserves the directory tree by document identifier. Do not put snippets into the HTML ZIP by default; publish them only when consumers need to reuse them.

## 4. Maven: Packaging HTML with the Assembly Plugin

Assume Asciidoctor Maven Plugin renders documentation into target/generated-docs. Create the descriptor src/assembly/api-docs.xml:

~~~xml
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/ASSEMBLY/2.2.0
          https://maven.apache.org/xsd/assembly-2.2.0.xsd">
    <id>api-docs</id>
    <formats>
        <format>zip</format>
    </formats>
    <includeBaseDirectory>false</includeBaseDirectory>
    <fileSets>
        <fileSet>
            <directory>${project.build.directory}/generated-docs</directory>
            <outputDirectory>/</outputDirectory>
        </fileSet>
    </fileSets>
</assembly>
~~~

Bind Maven Assembly Plugin in the package phase:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-assembly-plugin</artifactId>
    <version>${maven.assembly.plugin.version}</version>
    <executions>
        <execution>
            <id>package-api-docs</id>
            <phase>package</phase>
            <goals>
                <goal>single</goal>
            </goals>
            <configuration>
                <descriptors>
                    <descriptor>src/assembly/api-docs.xml</descriptor>
                </descriptors>
                <finalName>${project.artifactId}-${project.version}</finalName>
                <appendAssemblyId>true</appendAssemblyId>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

The maven.assembly.plugin.version property must be declared in the POM or parent POM. The package phase occurs after prepare-package; if Asciidoctor is bound to prepare-package, HTML is ready before assembly runs.

Run:

~~~bash
mvn clean package
~~~

Check the output in target/, for example:

~~~text
target/
├── generated-snippets/
├── generated-docs/
└── registration-api-1.0.0-api-docs.zip
~~~

The actual filename depends on finalName, appendAssemblyId, and plugin configuration. Inspect the archive after building to confirm index.html is at the expected root.

## 5. Attaching Docs Artifacts to a Maven Publication

If you need to publish docs under the application's Maven coordinates, you can attach the ZIP as a secondary artifact using Build Helper Maven Plugin:

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>${build.helper.plugin.version}</version>
    <executions>
        <execution>
            <id>attach-api-docs</id>
            <phase>package</phase>
            <goals>
                <goal>attach-artifact</goal>
            </goals>
            <configuration>
                <artifacts>
                    <artifact>
                        <file>${project.build.directory}/${project.build.finalName}-api-docs.zip</file>
                        <type>zip</type>
                        <classifier>api-docs</classifier>
                    </artifact>
                </artifacts>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

The file path must match the exact ZIP file created by Assembly Plugin. The artifact has the classifier api-docs, distinguishing it from the application's main JAR.

When the release pipeline runs mvn deploy, Maven can publish the main artifact along with the attached artifact to the configured repository. Verify package/local staging first before placing it into an approved release workflow.

## 6. Uploading Artifacts in CI

After the build creates ZIP/HTML/PDF, CI must upload the right path. Example with GitHub Actions:

~~~yaml
name: Build API documentation

on:
  pull_request:
  push:
    branches: [main]

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Build documentation
        run: ./gradlew clean test asciidoctor apiDocsZip

      - name: Upload documentation artifact
        uses: actions/upload-artifact@v4
        with:
          name: registration-api-docs
          path: build/distributions/registration-api-docs-*.zip
          if-no-files-found: error
          retention-days: 14
~~~

The example assumes the project has an apiDocsZip task and the archive path matches the pattern. If using Maven, substitute the build command and artifact path accordingly, such as mvn clean package and target/*-api-docs.zip.

if-no-files-found: error ensures the job fails if the build produces no artifact. Without this step, the pipeline could report success even with no documentation available to download.

### 6.1. CI Artifacts and Release Artifacts

Not every artifact uploaded from CI is a public artifact:

| Storage location | Purpose | Lifecycle |
| --- | --- | --- |
| CI job artifact | Pull request review, download build results, debug | Can have short retention |
| Release asset | Documentation tied to a release version | Retained per release policy |
| Maven/Gradle repository | Share artifacts by coordinates/version | Per repository policy |
| Static hosting | Serve documentation website to users | By version or alias |

Pull requests can upload an HTML ZIP for reviewers to preview. Only a release job after merge/tag should publish to the release repository or public website.

## 7. Verifying Artifacts Before Upload or Publishing

Do not check only that the build task returns exit code 0. Inspect the archive contents:

~~~bash
unzip -l build/distributions/registration-api-docs-*.zip
~~~

Extract to a temporary directory and confirm:

- index.html exists at the location users will open.
- CSS, JavaScript, images, and subpages are inside the archive.
- Internal links do not point to paths on a developer's machine.
- No pages are missing due to broken snippet includes.
- The artifact does not contain build/, target/, test logs, or unintended temporary files.

You can add a simple shell step in CI:

~~~bash
test -f build/docs/asciidoc/index.html
test -f build/distributions/registration-api-docs-html.zip
~~~

Adjust paths according to the actual configuration. Checking file existence is a basic step; for large websites, add a link checker or smoke test after extraction.

## 8. Versioning, Provenance, and Reproducibility

Documentation must be tied to the exact API version it describes. Artifacts should carry the application version or commit:

~~~text
registration-api-1.4.0-api-docs.zip
registration-api-1.4.0-api-snippets.zip
~~~

Principles:

1. Generate docs from the same commit/tag used to build the application.
2. Share the application's version property when naming artifacts.
3. Run a clean build in the release job so stale snippets are not picked up.
4. Store the commit SHA and version in release or artifact metadata.
5. Do not use the latest alias as the sole identifier for an immutable artifact.

If HTML is deployed under a versioned path, such as /docs/1.4.0/, users can look up older documentation matching the right API version. An alias /docs/latest/ can point to the newest version, but does not replace versioned archives.

## 9. Protecting Data in Generated Documentation

Snippets are generated from test requests/responses, so fixture data can appear in artifacts. Before publishing:

- Use dummy data, never real tokens, passwords, or customer information.
- Verify whether Authorization headers, cookies, and sensitive values are masked.
- Do not write secret logs or payloads into request/response snippets.
- Inspect attached files and multipart contents if tests perform uploads.
- Restrict access if artifacts contain internal endpoints or unannounced details.

If data must be hidden, configure Spring REST Docs preprocessors in tests to remove or replace appropriate headers/bodies before writing snippets. Do not hand-edit generated files after building to hide data; fix the tests/configuration and regenerate the artifact.

## 10. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Empty ZIP | Packaged before Asciidoctor or wrong source directory | Add dependency/phase and check output path |
| ZIP missing CSS/images | Only grabbed index.html | Package the entire HTML directory |
| CI succeeds yet no artifact exists | Wrong upload path or package task did not run | Fail on missing files and verify archive |
| Maven fails to attach ZIP | File path or classifier mismatch | Match Assembly output with Build Helper |
| Docs have wrong version | Built from different commit or stale snippets | Use clean build and version/commit metadata |
| Artifact leaks sensitive data | Fixtures contain secrets or request/response not preprocessed | Use dummy data and configure masking in tests |
| Broken links after extraction | Archive missing assets or wrong base directory | Check ZIP structure and relative links |
| Internal snippets published unintentionally | Packaged entire generated-snippets | Publish only HTML/PDF; keep snippets as separate artifact if needed |

## 11. Hands-On Exercise

In a Spring REST Docs project, create an HTML artifact for the GET /orders/{id} endpoint.

1. Write a MockMvc test generating request and response snippets.
2. Configure Asciidoctor to render into the build output directory.
3. With Gradle, create an apiDocsZip task; with Maven, create an Assembly descriptor and bind its execution after the render phase.
4. Configure CI to run a clean build, tests, render, and upload the ZIP.
5. Inspect the archive to verify index.html, CSS, and required pages are present.
6. Name the artifact using the application version and record the commit SHA.
7. Review snippets to ensure no tokens, cookies, or real data exist.
8. Create a release staging artifact and confirm the documentation can be opened after extraction.

**Completion criteria:** the artifact is created after tests and rendering succeed; contains all assets needed for reading; version/commit are traceable; CI fails when the artifact is missing; snippet data is safe for distribution.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Gradle User Manual — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Apache Maven Assembly Plugin — Usage](https://maven.apache.org/plugins/maven-assembly-plugin/usage.html)
- [Build Helper Maven Plugin — Attach Artifact](https://www.mojohaus.org/build-helper-maven-plugin/attach-artifact-mojo.html)
- [GitHub Actions — Uploading Build Artifacts](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts)
